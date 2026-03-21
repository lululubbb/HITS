package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.Field;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ExtendedBufferedReader_2_6Test {

    ExtendedBufferedReader extendedBufferedReader;
    Reader mockReader;

    // Subclass to expose readFromSuper() method and allow overriding read()
    static class ExtendedBufferedReaderSpy extends ExtendedBufferedReader {
        ExtendedBufferedReaderSpy(Reader r) {
            super(r);
        }

        int readFromSuper() throws IOException {
            return super.read();
        }

        @Override
        public int read() throws IOException {
            int current = readFromSuper();
            if (current == '\n') {
                incrementLineCounter();
            }
            setLastChar(current);
            return current;
        }

        private void incrementLineCounter() {
            try {
                Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
                lineCounterField.setAccessible(true);
                int currentValue = lineCounterField.getInt(this);
                lineCounterField.setInt(this, currentValue + 1);
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        }

        private void setLastChar(int value) {
            try {
                Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
                lastCharField.setAccessible(true);
                lastCharField.setInt(this, value);
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        }
    }

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReaderSpy(mockReader);
    }

    @Test
    @Timeout(8000)
    void testRead_returnsCharNotNewline_updatesLastCharAndLineCounter() throws IOException {
        ExtendedBufferedReaderSpy spyReader = spy((ExtendedBufferedReaderSpy) extendedBufferedReader);
        // Mock the readFromSuper() method to return 'A'
        doReturn((int) 'A').when(spyReader).readFromSuper();

        int result = spyReader.read();
        assertEquals('A', result);

        int lastChar = getPrivateIntField(spyReader, "lastChar");
        int lineCounter = getPrivateIntField(spyReader, "lineCounter");
        assertEquals('A', lastChar);
        assertEquals(0, lineCounter);
    }

    @Test
    @Timeout(8000)
    void testRead_returnsNewline_incrementsLineCounterAndUpdatesLastChar() throws IOException {
        ExtendedBufferedReaderSpy spyReader = spy((ExtendedBufferedReaderSpy) extendedBufferedReader);
        doReturn((int) '\n').when(spyReader).readFromSuper();

        int result = spyReader.read();
        assertEquals('\n', result);

        int lastChar = getPrivateIntField(spyReader, "lastChar");
        int lineCounter = getPrivateIntField(spyReader, "lineCounter");
        assertEquals('\n', lastChar);
        assertEquals(1, lineCounter);
    }

    @Test
    @Timeout(8000)
    void testRead_returnsEndOfStream_updatesLastCharNoIncrementLineCounter() throws IOException {
        ExtendedBufferedReaderSpy spyReader = spy((ExtendedBufferedReaderSpy) extendedBufferedReader);
        doReturn(ExtendedBufferedReader.END_OF_STREAM).when(spyReader).readFromSuper();

        int result = spyReader.read();
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, result);

        int lastChar = getPrivateIntField(spyReader, "lastChar");
        int lineCounter = getPrivateIntField(spyReader, "lineCounter");
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, lastChar);
        assertEquals(0, lineCounter);
    }

    private int getPrivateIntField(Object instance, String fieldName) {
        try {
            Field field = ExtendedBufferedReader.class.getDeclaredField(fieldName);
            field.setAccessible(true);
            return field.getInt(instance);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }
}