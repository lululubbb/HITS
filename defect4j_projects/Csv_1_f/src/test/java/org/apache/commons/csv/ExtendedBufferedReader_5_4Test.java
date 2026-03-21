package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.Field;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ExtendedBufferedReader_5_4Test {

    ExtendedBufferedReader extendedBufferedReader;
    Reader mockReader;

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReader(mockReader);
    }

    @Test
    @Timeout(8000)
    void testReadLine_NonNullNonEmptyLine() throws IOException, NoSuchFieldException, IllegalAccessException {
        ExtendedBufferedReader reader = new ExtendedBufferedReader(new java.io.StringReader("abc\n"));
        String line = reader.readLine();

        assertEquals("abc", line);

        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        int lastChar = (int) lastCharField.get(reader);
        assertEquals('c', lastChar);

        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        int lineCounter = (int) lineCounterField.get(reader);
        assertEquals(1, lineCounter);
    }

    @Test
    @Timeout(8000)
    void testReadLine_NonNullEmptyLine() throws IOException, NoSuchFieldException, IllegalAccessException {
        ExtendedBufferedReader reader = new ExtendedBufferedReader(new java.io.StringReader("\n"));
        String line = reader.readLine();

        assertEquals("", line);

        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        int lastChar = (int) lastCharField.get(reader);
        // lastChar should remain unchanged (default UNDEFINED = -2)
        assertEquals(ExtendedBufferedReader.UNDEFINED, lastChar);

        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        int lineCounter = (int) lineCounterField.get(reader);
        assertEquals(1, lineCounter);
    }

    @Test
    @Timeout(8000)
    void testReadLine_NullLine() throws IOException, NoSuchFieldException, IllegalAccessException {
        ExtendedBufferedReader reader = new ExtendedBufferedReader(new java.io.StringReader(""));
        String line = reader.readLine();

        assertNull(line);

        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        int lastChar = (int) lastCharField.get(reader);
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, lastChar);

        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        int lineCounter = (int) lineCounterField.get(reader);
        // lineCounter should not increment on null line
        assertEquals(0, lineCounter);
    }

    @Test
    @Timeout(8000)
    void testReadLine_IOException() throws IOException {
        Reader throwingReader = mock(Reader.class);
        ExtendedBufferedReader reader = new ExtendedBufferedReader(throwingReader);
        // Mock the underlying Reader to throw IOException on read()
        doThrow(new IOException("Test IO Exception")).when(throwingReader).read(any(char[].class), anyInt(), anyInt());

        IOException thrown = assertThrows(IOException.class, reader::readLine);
        assertEquals("Test IO Exception", thrown.getMessage());
    }
}