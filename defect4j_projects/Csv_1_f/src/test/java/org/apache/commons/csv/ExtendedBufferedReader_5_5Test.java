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
import org.mockito.Mockito;

class ExtendedBufferedReader_5_5Test {

    private Reader mockReader;
    private ExtendedBufferedReader extendedBufferedReader;

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReader(mockReader);
    }

    @Test
    @Timeout(8000)
    void testReadLine_NullLine() throws Exception {
        ExtendedBufferedReader spyReader = Mockito.spy(extendedBufferedReader);

        // Mock the super.readLine() by mocking the underlying Reader to return -1 on read()
        // so that super.readLine() returns null naturally.
        // Alternatively, mock readLine() on the underlying BufferedReader using spy.
        doReturn(null).when(spyReader).readLine();

        // To avoid recursion, use doReturn(null).when(spyReader).readLine() is not correct here,
        // because it mocks the method under test itself causing infinite recursion.
        // Instead, mock the underlying Reader to return -1 on read(), so super.readLine() returns null.

        // So let's reset spy and mock underlying reader properly:
        ExtendedBufferedReader reader = new ExtendedBufferedReader(mockReader);
        ExtendedBufferedReader spy = Mockito.spy(reader);

        // Mock underlying Reader to return -1 on read()
        doReturn(-1).when(mockReader).read();

        // Now call real method
        String line = spy.readLine();

        assertNull(line);

        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        int lastChar = lastCharField.getInt(spy);
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, lastChar);

        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        int lineCounter = lineCounterField.getInt(spy);
        assertEquals(0, lineCounter);
    }

    @Test
    @Timeout(8000)
    void testReadLine_EmptyLine() throws Exception {
        ExtendedBufferedReader reader = new ExtendedBufferedReader(mockReader);
        ExtendedBufferedReader spyReader = Mockito.spy(reader);

        // Mock underlying Reader to return '\n' immediately, so super.readLine() returns empty string
        doReturn((int) '\n').when(mockReader).read();

        String line = spyReader.readLine();

        assertEquals("", line);

        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        int lastChar = lastCharField.getInt(spyReader);
        assertEquals(ExtendedBufferedReader.UNDEFINED, lastChar);

        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        int lineCounter = lineCounterField.getInt(spyReader);
        assertEquals(1, lineCounter);
    }

    @Test
    @Timeout(8000)
    void testReadLine_NonEmptyLine() throws Exception {
        String testLine = "Hello, world!";

        // We will mock the underlying Reader to return characters of testLine followed by '\n' and then -1
        Reader realReader = new Reader() {
            private final char[] chars = (testLine + "\n").toCharArray();
            private int pos = 0;

            @Override
            public int read(char[] cbuf, int off, int len) {
                if (pos >= chars.length) {
                    return -1;
                }
                int count = Math.min(len, chars.length - pos);
                for (int i = 0; i < count; i++) {
                    cbuf[off + i] = chars[pos++];
                }
                return count;
            }

            @Override
            public void close() {
            }
        };

        ExtendedBufferedReader extendedReader = new ExtendedBufferedReader(realReader);
        ExtendedBufferedReader spyReader = Mockito.spy(extendedReader);

        String line = spyReader.readLine();

        assertEquals(testLine, line);

        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        int lastChar = lastCharField.getInt(spyReader);
        assertEquals(testLine.charAt(testLine.length() - 1), lastChar);

        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        int lineCounter = lineCounterField.getInt(spyReader);
        assertEquals(1, lineCounter);
    }
}