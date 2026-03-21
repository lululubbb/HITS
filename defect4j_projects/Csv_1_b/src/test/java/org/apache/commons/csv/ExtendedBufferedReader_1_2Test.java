package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ExtendedBufferedReader_1_2Test {

    private ExtendedBufferedReader extendedBufferedReader;
    private Reader mockReader;

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReader(mockReader);
    }

    @Test
    @Timeout(8000)
    void testConstructor() {
        assertNotNull(extendedBufferedReader);
    }

    @Test
    @Timeout(8000)
    void testRead_whenReaderReturnsChar() throws IOException {
        when(mockReader.read()).thenReturn((int) 'a');
        int ch = extendedBufferedReader.read();
        assertEquals('a', ch);
    }

    @Test
    @Timeout(8000)
    void testRead_whenReaderReturnsEndOfStream() throws IOException {
        when(mockReader.read()).thenReturn(-1);
        int ch = extendedBufferedReader.read();
        assertEquals(-1, ch);
    }

    @Test
    @Timeout(8000)
    void testRead_charArray() throws IOException {
        char[] buf = new char[5];
        when(mockReader.read(buf, 0, 5)).thenReturn(5);
        int readCount = extendedBufferedReader.read(buf, 0, 5);
        assertEquals(5, readCount);
    }

    @Test
    @Timeout(8000)
    void testRead_charArray_partial() throws IOException {
        char[] buf = new char[5];
        when(mockReader.read(buf, 1, 3)).thenReturn(3);
        int readCount = extendedBufferedReader.read(buf, 1, 3);
        assertEquals(3, readCount);
    }

    @Test
    @Timeout(8000)
    void testReadLine() throws IOException {
        Reader stringReader = new java.io.StringReader("line1\nline2\n");
        ExtendedBufferedReader reader = new ExtendedBufferedReader(stringReader);
        String line1 = reader.readLine();
        String line2 = reader.readLine();
        assertEquals("line1", line1);
        assertEquals("line2", line2);
    }

    @Test
    @Timeout(8000)
    void testReadAgain_viaReflection() throws NoSuchMethodException, InvocationTargetException, IllegalAccessException, IOException {
        Method readAgainMethod = ExtendedBufferedReader.class.getDeclaredMethod("readAgain");
        readAgainMethod.setAccessible(true);

        when(mockReader.read()).thenReturn((int) 'x');

        int result = (int) readAgainMethod.invoke(extendedBufferedReader);
        assertEquals('x', result);
    }

    @Test
    @Timeout(8000)
    void testLookAhead_viaReflection() throws NoSuchMethodException, InvocationTargetException, IllegalAccessException, IOException {
        Method lookAheadMethod = ExtendedBufferedReader.class.getDeclaredMethod("lookAhead");
        lookAheadMethod.setAccessible(true);

        when(mockReader.read()).thenReturn((int) 'y');
        int result = (int) lookAheadMethod.invoke(extendedBufferedReader);
        assertEquals('y', result);
    }

    @Test
    @Timeout(8000)
    void testGetLineNumber_viaReflection() throws NoSuchMethodException, InvocationTargetException, IllegalAccessException {
        Method getLineNumberMethod = ExtendedBufferedReader.class.getDeclaredMethod("getLineNumber");
        getLineNumberMethod.setAccessible(true);

        int lineNumber = (int) getLineNumberMethod.invoke(extendedBufferedReader);
        assertEquals(0, lineNumber);
    }
}